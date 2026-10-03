# alpha-0.58（2026-08-08）

## 变更

- **紧急修复：所有消息不再进入时间线**：
  - 根因：合成事件识别误用 `is_wake` / `is_at_or_wake_command` 作为特征——AstrBot 会对「@机器人 / 私聊 / 带唤醒词」的**真实消息**也置这些标记为 True（插件注册事件监听器即置位），导致所有消息被当作合成事件跳过捕获，时间线完全停止记录；
  - 修复：仅使用确定性特征——消息 ID 带合成前缀（`private_companion_` 等）、或 sender 与会话键相同；
  - 已验证：真实消息（is_wake=True）不再被跳过；合成事件仍可正确识别。

## 说明

- 版本备份：工作区 backup 目录下的 `astrbot_plugin_deepmemory_alpha-0.58`。
