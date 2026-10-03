# 为你篆刻的历史

`astrbot_plugin_deepmemory`（中文名：**为你篆刻的历史**）是面向 AstrBot 的长期记忆中枢插件。它把对话沉淀为结构化长期记忆，并提供记忆分区隔离、用户隔离、混合检索、记忆权重、自然衰减、批量导入导出、手动记忆增删改与可配置的 WebUI 仪表盘。

- 插件名：`astrbot_plugin_deepmemory`
- 中文名：`为你篆刻的历史`
- 版本：`alpha-0.91`
- AstrBot 版本：`>= 4.22.0`
- 编码要求：UTF-8
- 更新日志：见 [changelogs/](changelogs/)（每个版本一个 Markdown 文件）

## 核心能力

- **WebUI 仪表盘**：总览 / 记忆库 / 用户 / 检索测试 / 时间线 / 导入导出 / 维护 / 外观 / 日志 / 设置，十个页面；设置页可开关、配置全部功能。
- **手动记忆管理**：在导入导出页直接新增/编辑/删除记忆条目，可填写时间、地点、人物、总结、标签、重要度、归属用户/群等字段。
- **按 AstrBot 人格隔离**：每条记忆归属当前会话的 AstrBot 人格（Persona），在 AstrBot 中切换人格后记忆自然隔离；无需插件内管理人格。
- **按用户隔离**：私聊记忆只对归属用户可见；群聊记忆只对归属群可见；另有跨用户/跨群/公共记忆可见性开关。
- **记忆权重**：重要度由基础值、手动加分、置信度、新鲜度半衰期、访问频率共同参与召回排序，因子权重全部可配置。
- **记忆衰减**：长期未访问、重要度低的记忆按配置压缩为摘要（LLM）、归档或删除。
- **混合检索**：FTS 关键词（SQLite FTS5，trigram 分词支持中文子串）+ 可选 Embedding 语义召回 + 可选 Rerank 二阶段重排。
- **阶段总结**：私聊按「对话轮」（用户连续发言段 + 机器人连续回复段）计数，群聊按「事件条数」计数，达到阈值后由 LLM 生成一条带真实称呼的综合记忆；总结时会把当前会话的人格/用户提示词一并提供给 LLM 作为身份参考，避免记忆偏差；阈值全部可配置。
- **批量导入导出**：JSONL / JSON 全字段档案导出下载；上传预览 → 人格映射 → 去重 → 执行导入，导入前自动备份。
- **详尽的记忆字段**：每条记忆包含身份验证（主体/客体实体与验证来源）、时间戳（创建/更新/发生/最近召回）、内容与摘要、标签、权重分解、置信度、来源（插件/渠道/消息 ID）、生命周期、作用域、会话与归属用户/群、元数据扩展（地点、人物等）。
- **桥接接口**：为陪伴插件等外部插件提供 `get_deepmemory_bridge()` 公共接口，可写入、检索、管理记忆分区与维护任务。

## 安装

将插件目录放入 AstrBot 插件目录，目录名保持：

```text
astrbot_plugin_deepmemory
```

常见路径：`<astrbot_data>/data/plugins/astrbot_plugin_deepmemory`

运行数据默认位于 AstrBot 插件数据目录下的 `astrbot_plugin_deepmemory/`：

```text
deepmemory.db            # SQLite 主数据库（记忆/用户/时间线/向量）
exports/                 # 导出的记忆档案
imports/                 # 导入的临时文件
backups/                 # 导入/清空前自动备份的数据库
backgrounds/             # 上传的背景图片（bg.<ext>）
logs/                    # 插件运行时日志（deepmemory.log + 滚动备份）
appearance.json          # 外观配置（主题/明暗/背景）
```

> 注意：以上数据位于 AstrBot 数据目录（`<astrbot_data>/plugin_data/astrbot_plugin_deepmemory/`），与插件代码目录分离。更新插件版本不会清除这些数据（刻意设计）；如需清除背景图，在外观页点「清除背景」即可。

## 快速开始

1. 插件管理页启用插件并配置 `_conf_schema.json` 中的项（也可直接在 WebUI 设置页调整）。
2. 保持 `capture.enabled`、`summary.enabled`、`injection.enabled` 为开（群聊捕获 `capture.group_capture_mode` 默认 **off**，需要群聊记忆时再改为 related/all）。
3. 给 `summary.provider_id` 配置总结用的 LLM 提供商（留空则用当前会话模型）。
4. 初期 `retrieval.embedding_enabled` 保持关闭；记忆变多后再配置 Embedding Provider 并开启。
5. 有 Rerank Provider 时设置 `retrieval.rerank_provider_id`，`mode` 用 `auto`。
6. 打开 WebUI → 插件 → 深忆，进入仪表盘。

## 与陪伴插件（为你续写的故事）联动的注意事项

- 本插件为陪伴插件预留了公共桥接接口（见下文），由陪伴插件读取/写入记忆。
- **重要**：当连接「为你续写的故事」插件**并开启其消息拟人化托管功能时，务必将本插件的群聊捕获（`capture.group_capture_mode`）设置为 `off`**，否则两个插件会同时沉淀群聊记忆，产生重复、错乱的记忆混淆。
- 单独使用本插件、或未开启联动插件的消息拟人化托管功能时，不要求关闭群聊捕获，可自由选择 `off`/`related`/`all`。

## WebUI

仪表盘页面：

| 页面 | 功能 |
| :--- | :--- |
| 总览 | 记忆统计、类型/作用域分布、注入与嵌入状态 |
| 记忆库 | 搜索、筛选、分页浏览；详情弹窗可编辑内容/摘要/类型/人格/状态/权重并删除 |

| 用户 | 查看活跃用户、删除用户及其私聊记忆 |
| 检索测试 | 模拟私聊/群聊会话视角检索，验证隔离与混合召回 |
| 时间线 | 最近原始对话事件与总结状态 |
| 导入导出 | **手动记忆管理**（新增/编辑/删除，含时间、地点、人物、总结等字段）、全字段档案导出下载、上传预览 → 人格映射 → 去重 → 导入、导入历史 |
| 维护 | 运行衰减与保留清理、备份数据库 |
| 外观 | 明暗模式（跟随系统/明亮/暗色）、8 套完整配色主题（各含明暗两套变量）、自定义主色/辅色/背景板颜色、背景图片上传、透明度与模糊度调节、玻璃拟态效果 |
| 日志 | 插件运行时日志查看、级别过滤、自动刷新、清空日志文件 |
| 设置 | 全部配置模块可视化编辑：开关、数值、下拉、Provider 选择器，逐模块保存/恢复默认 |

## 配置说明

全部配置在 `_conf_schema.json` 定义，WebUI 设置页可动态修改并持久化（写入 AstrBot 配置目录下 `astrbot_plugin_deepmemory_config.json`）。

- `general`：总开关、默认记忆分区、时区、单条正文上限。
- `capture`：是否记录用户消息/Bot 回复、最短记录字数、群聊捕获模式（**默认 off**；related 只捕获与机器人相关消息；all 捕获全部）、身份记忆模板。
- `summary`：总结开关、**群聊总结开关（默认关）**、模型（主/备）、最少事件数、**按条数触发阈值**、按时间触发分钟、单次事件上限、输入/输出字数、超时。
- `injection`：注入开关、**每次召回条数 top_k**、最大注入字数、是否注入总结、短回复跳过、注入日志。
- `retrieval`：重排模式（basic/auto/rerank）、关键词权重、Embedding 开关与 Provider、相似度阈值/权重/扫描上限/超时、Rerank Provider 与候选倍率。
- `weights`：默认重要度、基础重要度权重、新鲜度权重与半衰期、访问频率权重与上限、手动加分、最小置信度、注入最低重要度。
- `isolation`：记忆分区/用户/群聊隔离开关、跨用户/跨群可见、公共记忆全局可见、是否允许用户切换记忆分区。
- `decay`：衰减开关、年龄/未访问天数、最大重要度与召回次数、衰减方式（compress/archive/delete）、批量、压缩模型与字数。
- `maintenance`：自动维护开关与间隔、已总结时间线保留天数、导入前备份、保留导出文件。
- `bridge`：桥接接口开关、接受外部写入、来源插件白名单。
- `tools`：模型主动回忆/主动记忆工具开关。

## 聊天命令

| 命令 | 说明 |
| :--- | :--- |
| `/deepmem status` | 查看状态 |
| `/deepmem search <关键词> [k]` | 检索当前会话可见记忆 |
| `/deepmem add <内容>` | 手动添加记忆 |
| `/deepmem recent [n]` | 最近记忆 |
| `/deepmem summarize` | 立即总结当前会话时间线 |
| `/deepmem delete <memory_id>` | 删除记忆 |
| `/deepmem personas` | 记忆分区列表 |
| `/deepmem persona <persona_id>` | 切换当前会话记忆分区 |
| `/deepmem maintenance` | 运行维护 |
| `/deepmem export` | 导出全部记忆 |
| `/deepmem help` | 帮助 |

管理类命令需要 ADMIN 权限。

## LLM 工具

模型可主动调用：

- `deepmem_recall`：按当前会话可见性检索记忆。
- `deepmem_remember`：写入一条长期记忆（只有返回 `ok=true` 才算保存成功）。

## 为陪伴插件预留的桥接接口

其他插件可以通过以下方式接入（下一个陪伴插件将使用此接口）：

```python
from astrbot_plugin_deepmemory.core.bridge import get_deepmemory_bridge

bridge = get_deepmemory_bridge()
if bridge is not None:
    # 写入记忆（返回 memory_id）
    memory_id = await bridge.add_memory(
        content="今晚和小明一起看电影",
        memory_type="event",
        session_context={
            "session_id": "aiocqhttp:FriendMessage:10001",
            "scope": "private",
            "platform": "aiocqhttp",
            "user_id": "10001",
            "user_name": "小明",
        },
        source_plugin="astrbot_plugin_private_companion",
    )
    # 检索（返回序列化记忆列表，含 score/reason）
    results = await bridge.search("电影", session_context={...}, top_k=5)
    # 生成可直接注入提示词的记忆包
    text = await bridge.compose_injection("电影", session_context={...})
    # 管理
    await bridge.update_importance(memory_id, 0.9)
    bridge.delete_memory(memory_id)
    bridge.list_personas()
    bridge.create_persona("tsundere", "傲娇形态")
    bridge.set_user_persona("aiocqhttp:10001", "tsundere")
    await bridge.run_maintenance()
```

桥接对象在 `bridge.enabled` 为开时注册；`bridge.accept_external_records` 控制外部写入，`allowed_source_plugins` 可限制来源插件白名单（逗号分隔）。

## 数据与隐私

- 私聊记忆默认只对归属用户可见，群聊记忆默认只对归属群可见；跨窗口可见需要显式打开对应开关。
- 每条记忆记录身份验证状态与验证来源（platform/system/admin/llm），导入的记忆可人工修正归属。
- 导出档案包含全部记忆字段，但**不包含** Provider 凭据与向量索引（向量需在目标环境重新生成）。
- 导入前自动备份数据库到 `data/backups`；清空全部数据同样先备份。

## 常见问题

- **中文检索不到？** 使用 SQLite FTS5 trigram 分词器（需 SQLite >= 3.34）；旧环境自动回退 unicode61 + LIKE 兜底，效果略弱。
- **为什么没有注入记忆？** 检查 `injection.enabled`、记忆是否被隔离规则过滤、`top_k` 是否过小、消息是否过短（短回复跳过）。
- **Rerank 配好了但没用上？** 看日志 `[DeepMemory] 重排完成/失败`；确认 `retrieval.mode=auto` 且 Provider 具备 `rerank()` 能力。
- **如何清空全部记忆？** 维护页有备份与清空入口（生产环境谨慎使用）。
