# alpha-0.13（2026-08-08）

## 修复

- **阶段总结报错 `'DeepMemoryService' object has no attribute '_provider_attempts'`**：
  - 根因：alpha-0.12 重构 `_llm_json` 时引用了 `_provider_attempts` 方法，但该方法从未在本插件中实现（冒烟测试通过 monkeypatch 掩盖了缺失，真实环境直接 AttributeError）。
  - 修复：补齐 `_provider_attempts` 实现——按「主模型 → 备用模型 → 当前会话模型」顺序收集可用 Provider，按 provider_id 与实例去重，全部不可用时返回空列表。
  - 新增真实链路单元测试：顺序、去重（当前会话与主模型同一实例时只尝试一次）、全部不可用三种场景。

## 说明

- 总结失败后时间线会完整保留（不标记已总结），修复后重载插件即可重新触发；也可用 `/deepmem summarize` 立即验证。
