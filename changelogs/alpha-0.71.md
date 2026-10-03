# alpha-0.71（2026-08-08）

## 变更

- **导出/导入包含用户列表**（修复迁移后第一轮认错人）：
  - 导出档案新增用户数据：JSON 格式顶层 `users` 字段；JSONL 格式首行为元数据行
    （`__deepmemory_meta__`，含 users）；
  - 导入时恢复用户（user_key/user_id/name/platform/persona 绑定），不再需要重新沉淀身份；
  - 旧格式（无 users/meta）导入完全兼容；预览导入跳过元数据行。
- **调试页「最近主链对话 Prompt」展示真实发送内容**：
  - 根因：主链请求记录在记忆注入**之前**生成，调试页显示的 prompt/上下文是注入前快照，
    因此看不到 `<DeepMemory-Context>` 注入块（日志却显示注入成功）；
  - 修复：注入完成后重新记录请求，调试页展示实际发送给 LLM 的内容（含记忆注入块）。
- 档案格式版本升至 version 2。

## 说明

- 专项验证：jsonl/json 导出含用户、导入恢复用户、旧格式兼容；完整回归通过。
- 版本备份：工作区 backup 目录下的 `astrbot_plugin_deepmemory_alpha-0.71`。
