# alpha-0.49（2026-08-08）

## 变更

- **发布前清理（可上传 GitHub 的干净状态）**：
  - 移除 changelog 中的本机路径（backup 目录绝对路径改为通用描述）。
  - 脱敏 changelog 中测试期残留的测试用户昵称、测试人格名（如「证毕」「人格-test」→「用户」「测试人格」）。
  - 保留正式内容：特别鸣谢页人物（deepseek / 证毕 / 二氧化硫）、DS 卡充值链接（功能需求）、README 中的 API 示例（通用占位）。
- **版本同步流程确认**：每次更新统一执行「work 更新插件 → astr 同步部署 → backup 按版本备份」。

## 其他

- 版本备份：工作区 backup 目录下的 `astrbot_plugin_deepmemory_alpha-0.49`。
