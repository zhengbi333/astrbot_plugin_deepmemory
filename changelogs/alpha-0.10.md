# alpha-0.10（2026-08-08）

## 修复

- **重载插件失败（Formatting field not found in record: 'plugin_tag'）**：
  - 根因：AstrBot 的 Dashboard 日志 handler 使用依赖 `plugin_tag` / `short_levelname` / `ansi_prefix` 等字段的标准 logging Formatter，这些字段由挂在 AstrBot 自身 logger 上的 enricher filter 注入；而沿 logger 链传播的记录**不会执行祖先 logger 的 filters**，导致插件日志记录缺少这些字段，格式化时抛错并使插件加载失败。
  - 修复：插件 logger 挂载等价的 `_PluginEnricherFilter`，为每条记录补齐 `plugin_tag=[Plug]`、`short_levelname`、`ansi_prefix/reset`、`source_file/line` 等字段，传播到 AstrBot 任何日志 handler 均安全。
  - 已用「模拟 AstrBot 严格 Formatter」的自动化测试验证：INFO/WARNING/ERROR 三条记录全部格式化成功。

## 说明

- 插件日志现在会正常出现在 AstrBot 控制台与 Dashboard 日志页（`[Plug]` 标记），同时写入插件日志文件。
