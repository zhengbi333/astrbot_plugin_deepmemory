# alpha-0.2（2026-08-07）

## 新增

- 插件正式更名为「为你篆刻的历史」。
- 导入导出页新增「手动记忆管理」：新增 / 编辑 / 删除记忆条目，可填写时间（datetime-local，自动转 UTC 存储、本地时区展示）、地点、人物、总结、标签、重要度、置信度、人格、范围、归属用户/群。
- 后端新增 `POST /memory/create`；`/memory/update` 支持 `occurred_at`、地点、人物字段；`/memories` 支持 `order_by`。
- 时间归一化：支持带/不带时区的时间字符串与时间戳，统一按 Asia/Shanghai 解释为 UTC 存储。
- 版本号引入 `alpha-x.y` 迭代机制，`core/service.py` 单点维护。

## 修复

- 插件图标不显示：AstrBot 固定读取插件目录下的 `logo.png`（`metadata.yaml` 的 `icon` 字段无效），已将图片复制为 `logo.png`。
- UI 内残留「深忆 / 深」品牌名：页面标题、侧边栏、命令输出全部改为「为你篆刻的历史」。
- 弹窗「取消」按钮无效：内联 `onclick` 在 ES module 中无法访问模块作用域函数，改为 `data-close` 事件委托。
- 记忆编辑清空地点/人物无效：`update_memory_fields` 的 metadata 由合并语义改为整体替换语义。

## 说明

- 手动新增采用 `merge_duplicates=False`，不会与已有记忆合并。
