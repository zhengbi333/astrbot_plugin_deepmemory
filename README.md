# 为你篆刻的历史（astrbot_plugin_deepmemory）

> **本插件由 AI 制作**（DeepSeek 与 DSH 协同开发，作者署名：证毕＆deepseek）。
>
> **重要声明：当前为测试版本（alpha），功能与稳定性仍在打磨中，不代表最终品质；建议正式使用前充分验证。**
>
> **这只是一个学生的尝试，技艺不精，还请海涵。** 欢迎指出问题或提供建议，我会尽力改进。

面向 AstrBot 的**长期记忆中枢**：把对话沉淀为结构化长期记忆，并提供记忆分区隔离、用户隔离、混合检索、记忆权重、自然衰减、批量导入导出、手动记忆增删改与可配置的 WebUI 仪表盘。

- 插件名：`astrbot_plugin_deepmemory`
- 中文名：为你篆刻的历史
- 版本：`alpha-0.87`
- 兼容：AstrBot `>= 4.22.0`
- 编码：UTF-8

## 安装

**方式一：本地放置**（推荐）

1. 将整个插件目录（**目录名保持 `astrbot_plugin_deepmemory` 不变**）放入 AstrBot 插件目录：
   ```text
   <astrbot_data>/data/plugins/astrbot_plugin_deepmemory
   ```
   常见路径示例：`<astrbot 安装目录>/data/plugins/astrbot_plugin_deepmemory`
2. 打开 AstrBot 管理面板 →「插件」→ 找到「为你篆刻的历史」→ **启用 / 重载**；
3. 在插件管理页配置 `_conf_schema.json` 中的项（也可在插件 WebUI「设置」页调整，全部自动保存）。

**方式二：Git 安装**：AstrBot 插件市场支持通过 Git 仓库安装，直接添加：

```text
https://github.com/zhengbi333/astrbot_plugin_deepmemory
```

**快速开始**：
- 保持 `capture.enabled`、`summary.enabled`、`injection.enabled` 为开（群聊捕获默认 `off`，需要群聊记忆时改为 `related`/`all`）；
- 给 `summary.provider_id` 配置总结用 LLM（留空则用当前会话模型）；
- 初期 `retrieval.embedding_enabled` 可关闭，记忆变多后再配置 Embedding Provider 开启；
- 打开 WebUI → 插件 → 深忆，进入仪表盘。

## 核心能力

- **混合检索**：SQLite FTS5（trigram，中文子串友好）+ 可选 Embedding 语义召回 + 可选 Rerank 二阶段重排；关键词/语义/重排权重与阈值全部可配。
- **记忆权重**：重要度由 基础值 + 手动加分 + 置信度 + 新鲜度（半衰期）+ 访问频率 共同参与排序；因子权重可调。
- **双层隔离**：按 AstrBot 人格（Persona）与按用户/群隔离；跨用户/跨群/公共记忆可见性开关；自然衰减（压缩/归档/删除）。
- **阶段总结**：私聊按「对话轮」（连续发言段配对）、群聊按事件条数；LLM 生成带真实称呼的综合记忆（人格/用户设定作为身份参考，避免记忆偏差）；轮完整性守卫防止"半轮总结"。
- **详情字段**：身份验证（主体/客体实体与验证来源）、时间戳族、标签、权重分解、置信度、来源、生命周期、作用域、会话与归属用户/群、元数据扩展（地点/人物等）。
- **批量导入导出**：JSONL / JSON 全字段档案；上传预览 → 人格/用户映射 → 指纹去重 → 执行导入；导入前自动备份。
- **聊天命令**：`/deepmem status|search|add|recent|summarize|delete|maintenance|export|personas|persona|help`（管理命令需 ADMIN）。
- **LLM 工具**：`deepmem_recall`（主动回忆当前会话可见记忆）/ `deepmem_remember`（主动写入长期记忆，返回 `ok=true` 才算落库）。
- **WebUI 仪表盘**：总览 / 记忆库 / 用户 / 检索测试 / 时间线 / 导入导出（含手动记忆管理）/ 维护 / 外观 / 日志 / 插件调试 / 设置 / 特别鸣谢；8 套配色主题 × 明暗 + 玻璃拟态背景。

## 与其他插件的协同（桥接接口）

为陪伴类插件提供公共桥接接口：

```python
from astrbot_plugin_deepmemory.core.bridge import get_deepmemory_bridge

bridge = get_deepmemory_bridge()   # 未启用/未加载时为 None
memory_id = await bridge.add_memory(content="...", memory_type="promise", session_context={...})
results = await bridge.search("关键词", session_context={...}, top_k=6)
text = await bridge.compose_injection("关键词", session_context={...})
bridge.set_injection_managed(True)     # 托管记忆注入（由外部插件注入，避免双份）
```

桥接开关与外部写入白名单在「插件协同桥接」中配置；`bridge_status()` 可供外部插件探测联动可用性。

> 当配合陪伴插件「为你续写的故事」并开启其消息拟人化托管时，请将本插件的群聊捕获设为 `off`，避免两插件重复沉淀群聊记忆。

## 数据与隐私

运行数据位于 AstrBot 插件数据目录 `astrbot_plugin_deepmemory/`（`deepmemory.db`、`exports/`、`imports/`、`backups/`、`backgrounds/`、`logs/`、`appearance.json`），与代码分离，更新插件不清数据。私聊记忆默认仅归属用户可见；导出档案不包含 Provider 凭据与向量索引。

## 致谢

本插件在开发过程中参考了以下开源插件的设计思路与能力边界（实现完全独立，不含其代码）：

- **我会牢牢记住你**（`astrbot_plugin_memory_companion`）by **menglimi**（https://github.com/menglimi）——长期记忆/分层检索/记忆迁移等领域的优秀实践，感谢作者；
- **我会永远陪着你**（`astrbot_plugin_private_companion`）by **menglimi**（https://github.com/menglimi）——陪伴体系的成熟设计，感谢作者。

感谢两位参考插件作者的技术分享；本插件与你自己的两个插件（记忆中枢/陪伴插件）经过独立设计，命名、算法、存储、界面均为原创，仅作功能参考，无代码复用。

## 鸣谢人物

特别感谢测试与陪伴：**证毕（QED）**、**DeepSeek（DS）**、**二氧化硫（SO2）**（详见插件内「特别鸣谢」页）。

---

*插件由 AI（DeepSeek 与 DSH）制作。如遇问题，欢迎反馈。*
