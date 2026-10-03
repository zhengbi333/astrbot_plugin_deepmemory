# alpha-0.80

## 修复：接管模式下 on_llm_request 永远被陪伴插件截胡——身份标识沉淀/主链捕获失效

- **用户反馈**：删掉身份标识记忆后再发消息，身份标识不再产生。
- **根因（AstrBot 钩子规则）**：钩子监听器按优先级顺序执行，任一监听器 `stop_event()` 后**后续监听器不再执行**——陪伴插件接管 `on_llm_request(priority=10000)` 先执行并 stop 传播；deepmemory 的 `on_llm_request(priority=-20)` 排其后 → **接管模式下永远收不到** → `handle_llm_request`（身份沉淀 `ensure_identity_memory`、主链捕获、prompt 记录）全部失效。此前那条身份记忆来自 17:58:01 主链真实请求（未被接管关闭）的场合；用户平时的接管聊天永不触发。
- **修复**：deepmemory `on_llm_request` priority `-20 → 10001`（早于陪伴插件）——先捕获/沉淀身份，再交接管；注入由托管管理（external_injection_managed）跳过，无副作用；时间线捕获本就走消息级钩子，不受影响。

## 验证
- deepmemory 冒烟系列 + 41 项全套回归（见部署输出）
