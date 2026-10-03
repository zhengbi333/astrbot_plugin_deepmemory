# alpha-0.73（2026-08-16）

## 变更

- **新增「外部托管注入」机制**（配合陪伴插件联动）：
  - `DeepMemoryService` 新增 `external_injection_managed` 标志；置 True 时，主链请求
    （`handle_llm_request`）不再自动注入记忆，但捕获、后台总结等其余逻辑不受影响。
  - 桥接接口新增两个方法：
    - `set_injection_managed(enabled)`：由外部插件（如「为你续写的故事」）声明是否
      托管记忆注入；
    - `inject_for_event(req, event)`：由外部插件调用，解析事件上下文后把记忆注入到
      指定请求（复用本插件自身的检索与注入格式，保证与自动注入一致）。
  - 用途：陪伴插件接管主链回复请求时，由它统一决定注入时机与内容，避免与记忆插件
    自动注入重复。

## 说明

- 单独使用本插件（未联动陪伴插件）时行为不变：记忆照常自动注入。
- 版本备份：工作区 backup 目录下的 `astrbot_plugin_deepmemory_alpha-0.73`。
