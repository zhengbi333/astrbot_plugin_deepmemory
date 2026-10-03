# alpha-0.53（2026-08-08）

## 变更

- **桥接接口增强（面向后续陪伴插件）**，新增能力：
  - 便捷写入：`record_bot_action`（Bot 自我行动/日程）、`record_persona_life`（拟人生活记忆）；
  - 读取：`list_recent_memories`（按会话/用户取最近记忆，不带检索词）、`get_timeline`（最近时间线）、`resolve_persona_for`（查询会话当前人格，与 AstrBot 一致）；
  - 管理：`get_persona`、`list_users`、`get_user`、`delete_user_memories`。
  - 原有能力不变：`add_memory`、`search/recall`、`compose_injection`、`get_memory`、`update_importance`、`delete_memory`、人格管理、`summarize_now`、维护、导入导出、`health/stats/coordination_status`。

## 说明

- 外部插件通过 `from astrbot_plugin_deepmemory.core.bridge import get_deepmemory_bridge()` 获取实例；写入走外部写入权限校验（`bridge.accept_external_records` + `allowed_source_plugins` 白名单）。
- 版本备份：工作区 backup 目录下的 `astrbot_plugin_deepmemory_alpha-0.53`。
