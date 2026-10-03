# alpha-0.50（2026-08-08）

## 新增

- **「作者的话」页面映射文档文件**：
  - 后端新增 `GET /author/talk`，读取插件目录 `Special_Thanks/` 下的 `.md` 文档（当前：`want_to_talk.md`）并返回内容与更新时间。
  - 页面内置轻量 Markdown 渲染（标题 / 粗体 / 斜体 / 行内代码 / 列表 / 段落 / 链接），改文档即更新页面，无需改代码。

## 说明

- 三处同步（work / astr / backup）与发布前个人信息清理流程保持执行。
- 版本备份：工作区 backup 目录下的 `astrbot_plugin_deepmemory_alpha-0.50`。
