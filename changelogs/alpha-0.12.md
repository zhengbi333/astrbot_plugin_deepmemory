# alpha-0.12（2026-08-08）

## 修复

- **阶段总结持续失败（LLM 调用失败但 error 为空 = 超时）**：
  - 从插件日志定位：`LLM 调用失败: source=primary prefix=summary error=`（空错误信息是 `asyncio.TimeoutError` 的特征），触发到失败恰好间隔 60 秒（`summary.provider_timeout_seconds`）。
  - 重构 `_llm_json`：按 **主模型 → 备用模型 → 当前会话模型** 的顺序逐个尝试，单个超时/失败自动尝试下一个；全部失败后记录 `LLM 全部尝试失败`（含尝试列表与最后错误）。
  - 超时日志改为明确文案（`LLM 调用超时(60s): source=...`），不再是无信息的空 error。
  - 清理了不再使用的 `_resolve_llm_provider`。

## 变更

- **「人格」术语全面更名为「记忆分区」**（UI 侧边栏、页面标题、创建/编辑弹窗、命令输出、设置页 schema、README、元数据）：
  - 记忆分区是插件内部的记忆隔离容器，**与 AstrBot 的人设/人格配置无关**（AstrBot 的人设作用于 LLM 提示词，本插件的分区只决定记忆归属与召回可见性）。
  - 侧边栏选项卡与页面均加入该说明，避免混淆。
  - 内部字段（persona_id）、数据库结构与对外桥接 API 保持不变，陪伴插件等下游不受影响。

## 说明

- 若总结仍失败：检查 `summary.provider_id` 选择的模型是否可用/是否过慢（可调大 `summary.provider_timeout_seconds`），或直接留空以使用当前会话模型（聊天正常则总结也会正常）。
