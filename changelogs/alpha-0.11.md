# alpha-0.11（2026-08-08）

## 修复

- **阶段总结/衰减压缩的 LLM 调用失败（'ProviderOpenAIOfficial' object has no attribute 'text'）**：
  - 根因：新版 AstrBot 的 Provider 接口已由 `text()` 改为 `text_chat(prompt=..., session_id=...)`（`text` 已移除），插件仍使用旧接口调用，导致总结模型调用直接抛错。
  - 修复：新增 `_call_provider_text` 兼容层——优先调用 `text_chat`，旧版 `text` 兜底，两者皆无时给出明确错误提示（提醒检查 `summary.provider_id` 配置的是否为可对话的 LLM Provider）。
  - 超时仍受 `summary.provider_timeout_seconds` 配置控制。
  - 已用模拟测试覆盖：新版 text_chat / 旧版 text / 同步返回 / 无接口抛错 四种情况。

## 说明

- 总结失败时日志会出现明确的失败原因（provider_no_output / 无 text_chat 接口等），可在 AstrBot 控制台或插件「日志」标签页查看。
- 若日志仍提示缺少 text_chat/text 接口，请在设置页确认 `summary.provider_id` 选择的是对话模型 Provider（而非 Embedding/Rerank 类 Provider）。
