# alpha-0.75

## 记忆「像人」升级（与陪伴插件 alpha-0.121 配套）

- **链接标题与要点**：`_describe_links` —— 抓取网页标题（零 Token）+ 模型一句话要点（拿不准只给标题、不编造）；时间线从「[链接] url」升级为「[链接] 标题：要点」；`capture.link_summary` 控制（默认开）。抓取失败仍回退 URL。
- **动图连贯理解**：`_caption_image` 检测 GIF → PIL 均匀抽 N 帧（`capture.gif_frames` 默认 3：首/中/尾）→ 同一次 `text_chat(image_urls=[多帧])` 理解动图整体表达；与陪伴插件行为一致。
- **复用陪伴插件转述**：`_extract_existing_image_captions` 除 AstrBot 的 `[Image: xxx]` 外，识别陪伴插件注入的「（图片转述：xxx / 对方发来的图片：xxx / 对方发了个表情包：xxx）」——同一张图不再被两个插件各识图一次。
- **总结媒体加权**：`SUMMARY_PROMPT_TEMPLATE` 增加媒体说明：`[图片]/[表情]/[文件]/[链接]/[视频]/[语音]` 标记代表多媒体内容，其中重要事实（文档关键内容、链接指向的重要内容、图片关键事物）应纳入总结；纯表情互动可不特意记录。

## 说明

- 单独使用本插件行为不变（媒体描述照常）；新开关仅影响多媒体内容的记忆表达。
- 版本备份：`astrbot_plugin_deepmemory_alpha-0.75`。