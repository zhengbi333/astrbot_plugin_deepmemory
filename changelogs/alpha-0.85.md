# alpha-0.85

## deepmemory 逐模块自检 · 第 3 轮（summary 阶段总结）

### 本轮做的事
1. **核清 summary 的完整链路**：`main.py:initialize()` → `service.start()` → 三个后台任务
   （`maintenance` / `embed_backfill` / **`summary_scan`**）→ `_summary_scan_loop()`（每 `scan_interval_seconds`）
   → `maybe_summarize_session()` → `_summarize_session_inner()`：
   `store.unsummarized_timeline()` → `_compose_events_text()`（含 `merge_consecutive`）
   → `_llm_json(prefix="summary")` → **三级 provider 回退**（主模型 → 备用模型 → 当前会话模型）
   → 写入记忆并标记已总结。另有按轮数阈值、按时间间隔、清空上下文前三条触发路径。
2. **实测 19 项配置的读取情况**：18 项在代码中有读取，**1 项未被读取**（下表）。

### 修正：`summary.summarize_on_bot_idle` 是"声明了却不生效"的配置
- 该项描述为「空闲时补总结」且**默认 true**，但全仓宽松检索（`bot_idle|idle`）**只命中
  `decay.decay_idle_days` 相关逻辑**，**没有任何地方读取 `summarize_on_bot_idle`**；
- 翻 `CHANGELOG.md` 与 `changelogs/` 也**没有它的实现记录** → 属**从未实现**（不是重构丢失）；
- **处置**：如实改写它的 hint，说明"当前版本尚未实现该分支，改了暂时没有效果，
  阶段总结现由四条路径触发"。**没有**贸然新写"空闲检测"逻辑——那属于新功能，
  会引入新的调度面，应由你决定是否要。

### 离线启动链验证（6/6，用于排查"钩子不触发"）
在**临时副本**上复现 AstrBot 的加载过程（`StarTools.get_data_dir` 改指副本，绝不动真实库）：
`DeepMemoryPlugin(context, config)` 实例化 ✅ → 数据目录解析与开库 ✅ →
`initialize()` → `service.start()` ✅ → 后台扫描任务 spawn（`_summary_scan_task` = pending）✅。
并核对 AstrBot 侧机制：`star_manager.py:1417` 是以**实例**调用 `initialize()`（`star_cls` 在 1222 行由
`star_cls_type(context=…, config=…)` 实例化）✅。
→ 结论：**代码层面没有能解释"钩子自 09-07 起未被调用"的缺陷**（累计已排除 7 项），根因需运行时控制台日志。

### 未改动其它逻辑
本版仅含上述"如实标注 + 版本号"，不改任何运行行为。
