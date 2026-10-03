# alpha-0.9（2026-08-07）

## 修复

- **插件日志不出现在 AstrBot 控制台**：此前插件日志使用独立 logger 且 `propagate=False`，只写入插件日志文件，不会进入 AstrBot 日志体系。现在改为使用 `astrbot.plugin_deepmemory` 命名空间的子 logger（propagate 保持默认），插件日志会同时出现在 AstrBot 控制台 / Dashboard 日志页与插件日志文件（`logs/deepmemory.log`），与 example 插件的可见性一致。

## 新增

- 阶段总结流程补全可见日志：
  - 触发总结时记录 INFO（会话 / 人格 / 事件数 / 自动或手动）。
  - 总结模型无输出、总结失败时记录原因。
  - 总结完成时记录生成条数与事件数。

## 说明

- 本机测试建议：
  - 插件页确认「为你篆刻的历史」已启用（若未启用，控制台将看不到任何插件日志）。
  - 在设置页把 `summary.trigger_event_count` 调低（如 6）或使用 `/deepmem summarize` 手动触发总结。
  - 通过 `/deepmem status` 查看未总结时间线数量；AstrBot 日志页与插件「日志」标签页可查看插件日志。
  - 本机同时装有 livingmemory / memory_companion / private_companion 等记忆类插件，测试时建议只启用本插件，避免事件过滤器互相干扰。
