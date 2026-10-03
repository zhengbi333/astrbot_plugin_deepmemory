# alpha-0.63（2026-08-08）

## 变更

- **修复导出记忆报「未找到该路由」**：
  - 根因：前端使用 `bridge.download`（GET + query 参数）下载导出文件，而后端 `/export` 路由仅注册 POST，
    GET 请求无法匹配路由；
  - 修复：路由改为 GET+POST 双支持，handler 兼容 query 参数与 JSON body（format/scope/persona_id）。
- **消息撤回同步时间线**：
  - 监听 OneBot 撤回通知（`group_recall` / `friend_recall`），从时间线移除被撤回的消息；
  - 用户消息与对应该消息 ID 的 Bot 回复（共用同一 message_id）一并移除；
  - 仅移除未总结部分（已总结进记忆的无法回滚，属预期）；非撤回通知不误伤。
  - 说明：撤回事件经 AstrBot 适配器转为普通事件进入 ALL 捕获过滤器，识别特征为
    `raw_message` 中的 `post_type=notice` + `notice_type=group_recall/friend_recall`。

## 说明

- 专项验证：撤回移除（含 bot 回复连带）、非撤回通知不误删、撤回 ID 提取；完整回归通过。
- 版本备份：工作区 backup 目录下的 `astrbot_plugin_deepmemory_alpha-0.63`。
