# alpha-0.57（2026-08-08）

## 变更

- **「图片/文档理解模型」改为下拉选择**：
  - 设置页 `capture.media_describe_provider_id` 由手填字符串改为下拉菜单，选项为 AstrBot 已配置/开启的 Provider（含类型与模型名）；
  - 下拉含「跟随默认（AstrBot 图片理解模型）」空选项，与其余 Provider 下拉（总结/嵌入/重排）风格统一。
- **留空时的默认模型与 AstrBot 对齐**：
  - 未配置时，优先使用 AstrBot 设置中的「图片理解模型」（`provider_settings.default_image_caption_provider_id`，读自 abconf 配置）；
  - 未设置或不可用时，再回退总结主备模型与当前会话模型。

## 说明

- 专项验证：默认模型读取（含无配置回退）、schema 标记、完整回归全过。
- 版本备份：工作区 backup 目录下的 `astrbot_plugin_deepmemory_alpha-0.57`。
