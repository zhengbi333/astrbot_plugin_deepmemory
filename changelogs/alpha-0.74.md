# alpha-0.74

## 新增：识别接口 `bridge_status()`

- `core/bridge.py` 新增模块级只读探活函数 `bridge_status()`：返回 availability、插件名、版本号、协同配置摘要（`accept_external_records` / `persona_isolation` / `user_isolation` / `injection_enabled`）。
- 供陪伴插件（storyteller alpha-0.116）记忆页「联动状态」卡展示：未加载桥接对象时给出精确原因（插件已停用 / 「插件协同桥接 → 启用桥接 API」被关闭）。
- 零副作用：只读配置与桥对象，不触发 LLM、不写库。

## 防御：自身消息防线

- 捕获入口新增 `_is_self_message`（sender == 自身 ID）识别，覆盖：
  - `handle_llm_request`（主链请求前捕获）
  - `handle_group_message`（群聊捕获）
  - `handle_message_capture`（私聊 ALL 捕获）
  - `handle_llm_response`（Bot 回复捕获）
- 目的：部分 OneBot 实现会把 Bot 自己发出的消息回传为 message 事件；若不识别会被当作「用户消息」捕获进时间线（角色错位，污染总结与记忆）。默认平台不上报，此为双保险。

## 说明

- 单独使用本插件行为不变；对第三方插件的捕获不影响。
- 版本备份：工作区 backup 目录下的 `astrbot_plugin_deepmemory_alpha-0.74`。